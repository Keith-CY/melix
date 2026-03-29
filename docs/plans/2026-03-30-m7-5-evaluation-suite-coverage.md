# M7.5 Evaluation-Suite Coverage

## Goal

Add the requested evaluation-suite coverage so Melix can measure accuracy and intelligence beyond serving throughput.

## Scope

- add the requested evaluation-suite set
- preserve one evaluation execution interface across suites
- keep suite metadata and scoring explicit

## Files

- update `services/mlx-worker-python/worker/engine/`
- update `services/mlx-worker-python/worker/productization/`
- update `docs/runbooks/`
- update `tests/integration/`

## Implementation Notes

- suites should remain individually selectable and composable into larger jobs
- scoring and normalization rules should be versioned per suite
- keep evaluation-family growth incremental and testable

## Verification

- targeted evaluation smoke commands for the supported suites
- `make py-test`

## Acceptance

- the supported suite list is implemented and discoverable
- suite execution and scoring are reproducible and test-covered
