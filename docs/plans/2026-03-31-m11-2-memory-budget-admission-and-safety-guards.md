# M11.2 Memory Budget Admission And Safety Guards

## Goal

Add virtual-memory budgeting and load-admission guards so large-model streaming remains safe and operator-visible.

## Scope

- add virtual-memory budget controls
- enforce unsafe-load rejection based on headroom policy
- publish budget and rejection metrics

## Files

- update `services/control-plane-swift/Sources/`
- update `services/mlx-text-worker-swift/Sources/Core/`
- update `services/mlx-worker-python/worker/`
- update `tests/integration/`

## Implementation Notes

- Budgeting should compose with existing process-memory enforcement instead of replacing it.
- Rejections must be explicit and diagnosable.
- Headroom policy should separate RAM pressure from SSD-backed recovery cost where possible.

## Verification

- `make swift-test`
- `make integration-test`

## Acceptance

- Virtual-memory budgets block unsafe loads before instability.
- Budget controls and rejection paths are measurable and test-covered.
