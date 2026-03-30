# M16.3 Temporary-Media Lifecycle, Cleanup, And Failure Recovery

## Goal

Control the lifecycle of temporary media artifacts created during video preprocessing and analysis so Melix does not leak files or hide cleanup failures.

## Scope

- track extracted frames, transcodes, and temporary analysis assets
- clean up temporary media deterministically on success, failure, and cancellation
- expose cleanup failures to operators and tests

## Files

- update `services/mlx-worker-python/worker/runtime/`
- update `services/mlx-worker-python/worker/engine/`
- update `tests/integration/`
- update `docs/runbooks/`

## Implementation Notes

- Cleanup should be explicit and observable rather than hidden inside best-effort worker-local finally blocks.
- Cancellation and timeout paths must receive the same cleanup guarantees as success paths.

## Verification

- `make py-test`
- `make integration-test`

## Acceptance

- Temporary media artifacts are cleaned up deterministically across terminal states.
- Cleanup failures are surfaced through stable state and test coverage.
