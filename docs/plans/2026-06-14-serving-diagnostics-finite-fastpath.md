# Serving diagnostics bound finite check fast path

## Summary

This Python-only performance slice is limited to the empty-attribute serving
diagnostics JSONL fast path in
`services/mlx-worker-python/worker/productization/serving_diagnostics.py`.
The behavior stays unchanged while avoiding repeated `math.isfinite` attribute
lookups for each retained debug event row.

## Registered PR-scoped probe

The affected path is covered by the registered PR-scoped performance probe
`serving-diagnostics-debug-queue-bounds` in
`infra/perf/pr_scoped_probes.json`. The probe has focused `test_command`,
`coverage_command`, and `probe_command` entries for:

- `services/mlx-worker-python/worker/productization/serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_serving_diagnostics.py`
- `services/mlx-worker-python/tests/test_pr_scoped_performance.py`
- `scripts/serving_diagnostics_queue_probe.py`

No registry change is required for this slice.

## Optimization slice

The JSONL writer already has a specialized bytearray extension path for
empty-attribute events. This slice binds `math.isfinite` once at module import
as `_IS_FINITE` and uses that bound callable in the direct and bytearray fast
helpers. This keeps the finite-duration guard in place for invalid values while
reducing per-event global attribute lookup overhead on the hot serialization
path.

## Verification plan

Run the registered focused test command, changed-scope coverage command, and the
registered probe locally on Linux. The PR-scoped performance workflow remains
the merge gate for base-vs-head validation.

## Success criteria

- Focused Python tests pass.
- Changed-scope coverage for touched files remains at or above 95%.
- Registered probe shows non-regressing or improved queue/serialization metrics.
- GitHub Actions and the PR-scoped performance workflow are green before merge.
