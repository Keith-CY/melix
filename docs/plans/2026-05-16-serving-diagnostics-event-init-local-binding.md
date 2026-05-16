# Serving Diagnostics Event Init Local Binding

## Slice

Reduce per-event construction overhead in the serving diagnostics debug queue path by binding `object.__setattr__` through the `ServingDiagnosticsEvent.__init__` default arguments instead of resolving the module-level binding inside every event construction.

## Probe Coverage

The affected path is covered by the registered PR-scoped probe `serving-diagnostics-debug-queue-bounds` in `infra/perf/pr_scoped_probes.json`. The probe defines focused `test_command`, `coverage_command`, and `probe_command` entries for `services/mlx-worker-python/worker/productization/serving_diagnostics.py`, the serving diagnostics unit tests, the PR-scoped probe tests, and `scripts/serving_diagnostics_queue_probe.py`.

## Verification Plan

- Run the focused registered test command for `serving-diagnostics-debug-queue-bounds`.
- Run the registered coverage command and confirm changed-scope coverage remains at least 95%.
- Run the registered probe locally on Linux against `origin/main` and this head worktree.
- Use GitHub Actions PR-scoped performance results as the merge gate after opening the PR.

## Expected Behavior

No artifact schema or diagnostics queue behavior changes. The slice only removes repeated per-event local rebinding overhead during `ServingDiagnosticsEvent` construction.
