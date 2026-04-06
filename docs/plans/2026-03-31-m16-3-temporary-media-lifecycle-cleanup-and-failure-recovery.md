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
- focused Python worker tests for temporary-media lifecycle, registry projection, and VLM runtime
  cleanup branches
- focused Swift HTTP gateway tests for OCR and VLM cleanup metrics
- focused integration tests for success and cancelled-generate cleanup paths

## Acceptance

- Temporary media artifacts are cleaned up deterministically across terminal states.
- Cleanup failures are surfaced through stable state and test coverage.

## Status

Completed. Melix now owns one explicit temporary-media session helper for multimodal analysis
artifacts, deterministic and MLX-backed VLM runtimes stage inline assets through that helper, the
worker runtime registry publishes cleanup counters through `RuntimeStats`, and the Swift control
plane projects cleanup evidence through OCR and VLM metrics. Focused worker, control-plane, and
integration coverage now proves success, cleanup-failure, and cancellation paths with changed-line
coverage at or above the repository gate for the touched executable scope.
