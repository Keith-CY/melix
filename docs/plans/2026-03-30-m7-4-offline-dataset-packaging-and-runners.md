# M7.4 Offline Dataset Packaging And Runners

## Goal

Package evaluation datasets locally and add offline runners so evaluation can run without external network dependence.

## Scope

- define local dataset packaging layout
- add offline evaluation runners
- preserve reproducibility and versioned dataset identity

## Files

- update `services/mlx-worker-python/worker/productization/`
- update `services/mlx-worker-python/worker/engine/`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- packaged datasets should remain versioned and discoverable
- evaluation runners should record which dataset package and sample mode they used
- avoid hidden online fetches in the default evaluation flow

## Verification

- `make py-test`
- offline evaluation smoke command for a packaged dataset

## Acceptance

- evaluation can run against locally packaged datasets
- dataset identity is explicit in evaluation outputs
