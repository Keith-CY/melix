# Serving Diagnostics Request Summary Slots Slice

## Scope

This slice keeps the existing serving diagnostics bundle behavior unchanged and
narrows the Python object allocation footprint for request summary records by
adding dataclass slots to `ServingDiagnosticsRequestSummary`.

## Probe Coverage

The affected path is already covered by the registered PR-scoped performance
probe `serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`.

The probe includes:

- `test_command` covering `services/mlx-worker-python/tests/test_serving_diagnostics.py`
  and PR-scoped probe selection/script tests.
- `coverage_command` replaying the same focused test set under coverage.
- `probe_command` invoking `scripts/serving_diagnostics_queue_probe.py` with
  command-json metrics.

## Implementation Plan

1. Add `slots=True` to `ServingDiagnosticsRequestSummary`.
2. Keep serialization keys and value coercion unchanged.
3. Run the focused registered tests, changed-scope coverage, and registered
   probe locally on Linux.
4. Accept only if behavior remains stable and the registered probe shows a
   non-regressing or improved direction.

## Validation Boundary

This is a Python-only slice and can be locally verified on Linux. No Swift
runtime effect is claimed for this slice.
